"""Zurg-compatible release-name and keyless placement helpers.

This module is intentionally shaped by the current Zurg reference behavior:

  internal/releasename/releasename.go
  internal/releasename/numbering.go
  internal/torrent/dmmplacefree.go

Scud is an independent Python implementation for local files. Zurg remains the
reference implementation: when placement precedence or acceptance rules differ,
Scud should be changed to match Zurg. Local-library semantics are the one
intentional difference: a configured TV root already tells Scud that an item is
TV even if the top-level series folder itself has no SxxEyy marker.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re

VIDEO_EXT_RE = re.compile(r"(?i)\.(mkv|mp4|avi|m4v|ts|m2ts|wmv|mov|webm|nzb|torrent)$")
VIDEO_FILE_RE = re.compile(r"(?i)\.(mkv|mp4|avi|m4v|ts|m2ts|wmv|mov|webm|mpg|mpeg)$")
LEADING_GROUPS = re.compile(r"^(\s*\[[^\]]*\]\s*)+")
EPISODE_MARKER = re.compile(r"(?i)(?:^|[^a-z0-9])s\d{1,2} ?e\d{1,3}")
CROSS_MARKER = re.compile(r"(?i)(?:^|[^a-z0-9])(\d{1,2})x(\d{2,3})(?:[^a-z0-9]|$)")
PACK_MARKER = re.compile(r"(?i)(?:^|[^a-z0-9])s(\d{1,2})(?: ?- ?s?(\d{1,2}))?(?:[^a-z0-9]|$)")
SEASON_WORD = re.compile(r"(?i)(?:^|[^a-z0-9])season ?(\d{1,2})(?: ?- ?(\d{1,2}))?(?:[^a-z0-9]|$)")
EPISODE_AFTER_SEASON = re.compile(r"^ - (\d{1,4})((?: \d)?)(?:[^0-9a-z]|$)")
ABSOLUTE_MARKER = re.compile(r"(?i)(?:^|[^a-z0-9])ep? ?(\d{2,4})(?:[^a-z0-9]|$)")
QUALITY_TOKENS = re.compile(r"(?i)(?:^|[^a-z0-9])(2160p|1080p|1080i|720p|576p|480p|\d{3,4}x\d{3,4}|4k|uhd|remux|blu ?ray|bdrip|brrip|bdremux|bd|web ?dl|webrip|web|hdtv|dvdrip|dvd|x264|x265|h ?264|h ?265|hevc|avc|10bit|hdr|proper|repack|multi|complete)(?:[^a-z0-9]|$)")
SAMPLE_NAME = re.compile(r"(?i)(?:^|[^a-z0-9])sample(?:[^a-z0-9]|$)")

REMUX_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:remux|bdremux)(?:[^a-z0-9]|$)")
BLURAY_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:blu ?ray|bdrip|brrip|bdmux|bd)(?:[^a-z0-9]|$)")
WEBRIP_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])web ?rip(?:[^a-z0-9]|$)")
WEBDL_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:web ?dl|web|amzn|nf|dsnp|hmax|atvp|hulu|pcok|max)(?:[^a-z0-9]|$)")
HDTV_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:hdtv|pdtv|sdtv)(?:[^a-z0-9]|$)")
DVD_SOURCE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:dvdrip|dvd ?r|dvd)(?:[^a-z0-9]|$)")

SEASON_EPISODE_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])s(\d{1,2})[ ._-]*e(?:p(?:isode)?)?[ ._-]?(\d{1,3})((?:[ ._-]*(?:plus|and|\+|&)[ ._-]*(?:e(?:p(?:isode)?)?[ ._-]*)?\d{1,3}|[ ._-]*[-~][ ._-]*(?:e(?:p(?:isode)?)?[ ._-]*)?\d{1,3}|[ ._-]*e(?:p(?:isode)?)?[ ._-]*\d{1,3})*)(?:v\d{1,2})?(?:[^a-z0-9]|$)")
SPELLED_EPISODE_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])season[ ._-]?(\d{1,2})[ ._-]+(?:e|ep\.?|episode)[ ._-]?(\d{1,3})(?:[ ._]?[-~][ ._]?e?(\d{1,3}))?(?:[^a-z0-9]|$)")
CROSS_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])(\d{1,2})x(\d{2,3})(?:[^a-z0-9]|$)")
SEASON_MARKERS = [
    re.compile(r"(?i)(?:^|[^a-z0-9])s(\d{1,2})"),
    re.compile(r"(?i)(?:^|[^a-z0-9])season[ ._-]?(\d{1,2})"),
    re.compile(r"(?i)(?:^|[^a-z0-9])(\d{1,2})(?:st|nd|rd|th)[ ._-]+season"),
]
MULTI_SEASON_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])(?:s\d{1,2}[ ._]?-[ ._]?s\d{1,2}|s\d{1,2}-\d{1,2}|seasons?[ ._]?\d{1,2}(?:[-~]\d{1,2}|[ ._]?(?:&|\+|,|to|and)[ ._]?\d{1,2}))(?:[^a-z0-9]|$)")
PARTIAL_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])(?:part|pt|vol(?:ume)?|cour)[ ._]*\d")
ORDINAL_BEFORE_PATTERN = re.compile(r"(?i)\d(?:st|nd|rd|th)[ ._-]+$")
DATE_PATTERN = re.compile(r"(?:^|[^0-9])((?:19|20)\d{2})[ ._-](0[1-9]|1[0-2])[ ._-](0[1-9]|[12]\d|3[01])(?:[^0-9]|$)")
DASH_NUMBER_PATTERN = re.compile(r"(?i)(?:^|[ _])-[ _]+(\d{2,4})(?:v\d{1,2})?(?:[ _]*[-~][ _]*(\d{2,4})(?:v\d{1,2})?)?")
BRACKET_RANGE_PATTERN = re.compile(r"(?i)\((?:ep(?:isodes?)?\.?[ ._]?)?(\d{2,4})[ ._]*[-~][ ._]*(\d{2,4})\)")
AFTER_SEASON_PATTERN = re.compile(r"(?i)^[ ._)\]\-]*(\d{2,3})(?:v\d{1,2})?(?:[ _]*[-~][ _]*(\d{2,3})(?:v\d{1,2})?)?")
EXTRAS_PATTERN = re.compile(r"(?i)(?:^|[^a-z0-9])(?:ova|oad|oav|specials?|sp|ncop|nced|creditless|recap|preview|mini|pv|menu|trailer|teaser|bonus)(?:[^a-z]|$)")

@dataclass
class Numbering:
    season: int = 0
    seasons: int = 0
    first: int = 0
    last: int = 0
    absolute: bool = False
    partial: bool = False
    aired: str = ""
    unclear: bool = False
    season_unsure: bool = False

    def span(self):
        if self.unclear or self.seasons > 1 or self.aired or self.first <= 0 or self.last < self.first or self.last-self.first > 200:
            return None
        season = 1 if self.absolute else self.season
        return season, list(range(self.first, self.last+1))

@dataclass
class ParsedName:
    title: str = ""
    title_display: str = ""
    year: int = 0
    show: bool = False
    seasons: list[int] = field(default_factory=list)
    episodes: dict[int,list[int]] = field(default_factory=dict)
    resolution: str = ""
    source: str = ""


def spaced(name: str) -> str:
    s=VIDEO_EXT_RE.sub("",name.strip())
    s=LEADING_GROUPS.sub("",s)
    s=re.sub(r"[._\[\](){}]+"," ",s)
    return " ".join(s.split())


def fold(title: str) -> str:
    title=title.lower().replace("'","").replace("’","").replace("`","").replace("&"," and ")
    out=[]; space=True
    for ch in title:
        if ch.isalnum(): out.append(ch); space=False
        elif not space: out.append(' '); space=True
    return ''.join(out).strip()


def bare_title(title:str)->str:
    title=fold(title)
    for article in ("the ","a ","an "):
        if title.startswith(article): return title[len(article):]
    return title


def is_year(token:str)->bool:
    return len(token)==4 and (token.startswith('19') or token.startswith('20')) and token.isdigit()


def dash_episode(season:str,rest:str,always:bool)->bool:
    m=EPISODE_AFTER_SEASON.search(rest)
    if not m:return False
    return always or season.lstrip('0')!='1' or m.group(1).startswith('0') or len(m.group(1))>=3 or bool(m.group(2))


def _marked_seasons(title:str):
    found=[]
    for i,pattern in enumerate(SEASON_MARKERS):
        for m in pattern.finditer(title):
            end=m.end()
            if end < len(title) and title[end].isalnum():
                continue
            if i==1:
                word=m.start()
                while word < len(title) and not title[word].isalpha(): word+=1
                if ORDINAL_BEFORE_PATTERN.search(title[:word]): continue
            found.append((int(m.group(1)),end,i==0))
    return sorted(found,key=lambda x:x[1])


def _number_ends(title:str,i:int)->bool:
    if i>=len(title):return True
    c=title[i]
    if c in ' []()_,':return True
    if c=='.':return i+1>=len(title) or not title[i+1].isdigit()
    return False


def _looks_like_year(s:str)->bool:
    return len(s)==4 and (s.startswith('19') or s.startswith('20'))


def _anime_number(title:str,markers):
    if EXTRAS_PATTERN.search(title):return None
    candidates=[]
    def consider(m,offset=0):
        if not m:return
        end=m.end()
        if not _number_ends(title,end):return
        a=m.group(1); b=m.group(2) or a
        if _looks_like_year(a) or _looks_like_year(b):return
        candidates.append((m.start(1),int(a),int(b)))
    for m in DASH_NUMBER_PATTERN.finditer(title): consider(m)
    for m in BRACKET_RANGE_PATTERN.finditer(title): consider(m)
    for season,end,token in markers:
        m=AFTER_SEASON_PATTERN.search(title[end:])
        if not m:continue
        # translate the match coordinates to the original string
        class Proxy:
            def group(self,n): return m.group(n)
            def start(self,n=0): return end+m.start(n)
            def end(self,n=0): return end+m.end(n)
        p=Proxy()
        rest=title[p.end():].lstrip(' ._').lower()
        if rest.startswith('bit'):continue
        if p.group(1) in {'360','480','576','720'}:continue
        consider(p)
    if not candidates:return None
    start,first,last=min(candidates,key=lambda x:x[0])
    before=None
    for marker in markers:
        if marker[1] <= start: before=marker
    if before:
        season=before[0]; unsure=(not before[2]) or any(c in title[before[1]:start] for c in ')]')
        return start,first,last,season,False,unsure,False
    if markers:
        return start,first,last,0,False,False,True
    return start,first,last,0,True,False,False


def read_numbering(title:str)->Numbering:
    n=Numbering(); markers=_marked_seasons(title); seasons={m[0] for m in markers}
    if MULTI_SEASON_PATTERN.search(title):seasons.add(-1)
    n.partial=bool(PARTIAL_PATTERN.search(title))
    def done():
        n.seasons=len(seasons)
        if n.first>n.last:n.unclear=True
        return n
    m=SEASON_EPISODE_PATTERN.search(title)
    if m:
        n.season=int(m.group(1)); n.first=n.last=int(m.group(2)); more=re.findall(r"\d{1,3}",m.group(3) or '')
        if more:n.last=int(more[-1])
        if re.search(r'(?i)plus|and|[+&]',m.group(3) or '') and n.last-n.first!=len(more):n.unclear=True
        seasons.add(n.season);return done()
    m=SPELLED_EPISODE_PATTERN.search(title)
    if m:
        n.season=int(m.group(1)); n.first=n.last=int(m.group(2));
        if m.group(3):n.last=int(m.group(3))
        seasons.add(n.season);return done()
    m=CROSS_PATTERN.search(title)
    if m and m.group(2) not in ('264','265') and int(m.group(1))>0:
        n.season=int(m.group(1)); n.first=n.last=int(m.group(2));seasons.add(n.season);return done()
    m=DATE_PATTERN.search(title)
    if m:
        n.aired=f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if markers:n.season=markers[0][0]
        return done()
    anime=_anime_number(title,markers)
    if anime:
        _,n.first,n.last,n.season,n.absolute,n.season_unsure,n.unclear=anime
        return done()
    if markers:n.season=markers[0][0]
    return done()


def season_episodes(name:str):
    n=read_numbering(name); span=n.span()
    if not span or n.absolute or n.season_unsure:return {}
    season,eps=span; return {season:eps}


def episodes_in(name:str):
    if not VIDEO_FILE_RE.search(name) or SAMPLE_NAME.search(name):return {}
    return season_episodes(name)


def parse_name(name:str)->ParsedName:
    s=spaced(name); cut=len(s); episodes={}
    def mark(at):
        nonlocal cut
        cut=min(cut,at)
    episode_marks=list(EPISODE_MARKER.finditer(s))
    if not episode_marks:
        for m in CROSS_MARKER.finditer(s):
            season=int(m.group(1))
            if 0<season<=50:episode_marks.append(m)
    for m in episode_marks:mark(m.start())
    for season,eps in season_episodes(name).items(): episodes.setdefault(season,[]).extend(eps)
    numbering=read_numbering(name)
    episode=numbering.season_unsure and numbering.first>0 and numbering.seasons==1
    seasons=[]
    if not episode_marks:
        for pattern in (PACK_MARKER,SEASON_WORD):
            for m in pattern.finditer(s):
                mark(m.start())
                if episodes:continue
                from_s=int(m.group(1)); to_s=int(m.group(2)) if m.group(2) else from_s
                if episode and not m.group(2):continue
                rest=s[m.end(1):]
                if dash_episode(m.group(1),rest,pattern is PACK_MARKER or bool(VIDEO_EXT_RE.search(name))):
                    episode=True;continue
                if to_s<from_s or to_s-from_s>50:to_s=from_s
                for season in range(from_s,to_s+1):
                    if season not in seasons:seasons.append(season)
    show=bool(episodes or seasons or episode_marks or episode)
    if not show:
        m=ABSOLUTE_MARKER.search(s)
        if m and m.start()>0:show=True;mark(m.start())
    m=QUALITY_TOKENS.search(s)
    if m:mark(m.start())
    year=0;year_at=-1;offset=0
    for token in s.split(' '):
        at=offset;offset+=len(token)+1
        if at==0 or not is_year(token):continue
        y=int(token)
        if at<cut:year,year_at=y,at;continue
        if year==0:year=y
        break
    if year_at>=0:mark(year_at)
    raw_title=s[:cut].strip(); title=fold(raw_title)
    resolution=''
    qm=re.search(r"(?i)(2160p|1080p|1080i|720p|576p|480p|4k|uhd)",s)
    if qm:resolution=qm.group(1).lower().replace('4k','2160p').replace('uhd','2160p')
    source=''
    for rx,label in ((REMUX_SOURCE,'remux'),(WEBRIP_SOURCE,'webrip'),(BLURAY_SOURCE,'bluray'),(HDTV_SOURCE,'hdtv'),(WEBDL_SOURCE,'webdl'),(DVD_SOURCE,'dvd')):
        if rx.search(s):source=label;break
    return ParsedName(title=title,title_display=raw_title,year=year,show=show,seasons=sorted(seasons),episodes=episodes,resolution=resolution,source=source)


def absolute_episode(parsed:ParsedName)->ParsedName:
    if parsed.show or parsed.year:
        return parsed
    words=parsed.title_display.split()
    for i,word in enumerate(words):
        if word.lower() in ('episode','ep') and i>0 and i+1<len(words) and words[i+1].isdigit() and len(words[i+1])<=4:
            title=' '.join(words[:i]); parsed.title_display=title;parsed.title=fold(title);parsed.show=True;return parsed
    if len(words)>=2 and words[-1].isdigit() and len(words[-1])<=4:
        last=words[-1];year=len(last)==4 and (last.startswith('19') or last.startswith('20'))
        if not year and (last.startswith('0') or len(last)>=3):
            title=' '.join(words[:-1]);parsed.title_display=title;parsed.title=fold(title);parsed.show=True
    return parsed


def title_search_keyword(parsed:ParsedName)->str:
    if not parsed.title or (parsed.year==0 and not parsed.show and not parsed.resolution and not parsed.source):return ''
    return f"{parsed.title} {'show' if parsed.show else 'movie'}"


def pick_title(results:list[dict],parsed:ParsedName):
    want=bare_title(parsed.title);kind='show' if parsed.show else 'movie';best=None;best_off=2
    for r in results:
        imdb=str(r.get('imdbid') or '')
        if r.get('type')!=kind or not imdb.startswith('tt') or bare_title(str(r.get('searchTitle') or ''))!=want:continue
        if not parsed.year:return r
        try:off=abs(int(r.get('year') or 0)-parsed.year)
        except Exception:continue
        if off<best_off:best,best_off=r,off
    return best
