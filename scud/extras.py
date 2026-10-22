# Zurg references: /internal/rexfeed/library.go and /internal/torrent/extras.go (explicit extra kinds).
"""Recognise local bonus videos without turning numbered specials into clips."""
import re
from pathlib import PurePosixPath

FOLDERS={'extras':'other','extra':'other','bonus':'other','bonus features':'featurette','featurettes':'featurette','featurette':'featurette','deleted scenes':'deleted','behind the scenes':'behindthescenes','interviews':'interview','trailers':'trailer','specials':'other','special features':'featurette'}
TYPES=[(r'\bdeleted\s+scenes?\b','deleted'),(r'\b(?:behind\s+the\s+scenes|making\s+of|bloopers?)\b','behindthescenes'),(r'\binterviews?\b','interview'),(r'\b(?:trailers?|teasers?)\b','trailer'),(r'\bfeaturettes?\b','featurette'),(r'\bcreditless\s+openings?\b','opening'),(r'\bcreditless\s+endings?\b','ending')]

def extra_type(row):
    if not row:return None
    # Numbered TV specials (including season zero) retain their episode metadata.
    if row.get('kind')=='show' and row.get('season') is not None and row.get('episode') is not None:return None
    parts=PurePosixPath(row.get('relpath','')).parts
    folders=[' '.join(re.sub(r'[._-]+',' ',part.lower()).split()) for part in parts[1:-1]]
    kind=next((FOLDERS[part] for part in folders if part in FOLDERS),None)
    stem=re.sub(r'[._-]+',' ',PurePosixPath(row.get('relpath','')).stem.lower())
    # A title at the library root is never classified by words in its name alone.
    if kind is None and len(parts)<3:return None
    for pattern,value in TYPES:
        if re.search(pattern,stem):return value
    return kind

def identity(row):return {(key,str(row[key])) for key in ('imdb_id','tmdb_id','tvdb_id') if row.get(key)}
def group_key(row):return row['library_id'],row['relpath'].split('/')[0]
