"""Verify native source items against the library Rex actually stores them in."""
from __future__ import annotations
import time
from .rex import RexClient, RexError

class RexReceipts:
    def __init__(self, app):
        self.app=app
        self.locations={}
        self.library_names={}
        self.checked=None
        self.error=''
        self.checking=False

    def refresh(self):
        self.checking=True
        try:
            rex=RexClient(self.app.config,self.app.log)
            response=rex.session.get(f"{rex.base}/rex/feed/{self.app.config.get('rex_source','scud')}/items",headers=rex.headers(),timeout=60)
            if not response.ok:raise RexError(f'Cannot check received media (HTTP {response.status_code}).')
            items=[item for item in response.json().get('items',[]) if not item.get('deleted') and item.get('ratingKey')]
            keys=list({str(item['ratingKey']) for item in items})
            sections={};files={}
            for offset in range(0,len(keys),100):
                if self.app.scanner.stop_evt.is_set():return
                response=rex.session.get(rex.base+'/library/metadata/'+','.join(keys[offset:offset+100]),headers=rex.headers(),timeout=60)
                if not response.ok:raise RexError(f'Cannot verify Rex libraries (HTTP {response.status_code}).')
                for row in response.json().get('MediaContainer',{}).get('Metadata',[]):
                    if not row.get('deletedAt'):
                        key=str(row['ratingKey']);sections[key]=str(row.get('librarySectionID') or '')
                        files[key]={part.get('file') for media in row.get('Media',[]) for part in media.get('Part',[])}
            # Clips intentionally expose no librarySectionID. Their section's
            # extras listing proves ownership without accessing Rex's database.
            if any(not value for value in sections.values()):
                for library in self.app.config.get('libraries',[]):
                    key=str(library.get('rex_library_key') or '')
                    if not key:continue
                    response=rex.session.get(rex.base+'/library/sections/'+key+'/extras/all',headers=rex.headers(),timeout=60)
                    if not response.ok:raise RexError(f'Cannot verify Rex extras (HTTP {response.status_code}).')
                    for clip in response.json().get('MediaContainer',{}).get('Metadata',[]):
                        rating=str(clip.get('ratingKey') or '')
                        if rating in sections:sections[rating]=key
            response=rex.session.get(rex.base+'/library/sections',headers=rex.headers(),timeout=30)
            if response.ok:self.library_names={str(section['key']):section.get('title','another Rex library') for section in response.json().get('MediaContainer',{}).get('Directory',[])}
            self.locations={item['id']:sections[str(item['ratingKey'])] for item in items if str(item['ratingKey']) in sections and item.get('file') in files.get(str(item['ratingKey']),set())}
            self.checked=time.time();self.error=''
        except Exception as error:
            self.error=str(error)
            self.app.log.warning('Rex receipt check failed: %s',error)
        finally:self.checking=False

    def state(self,row):
        if not self.app.scanner.publishable(row):return 'withheld'
        if self.checked is None or self.error:return 'unknown'
        actual=self.locations.get(self.app.scanner.feed_id(row))
        target=next((str(lib.get('rex_library_key') or '') for lib in self.app.config.get('libraries',[]) if lib['id']==row['library_id']),'')
        if actual is None:return 'pending'
        return 'received' if target and actual==target else 'other_library'

    def summary(self):
        counts={state:0 for state in ('received','pending','withheld','other_library','unknown')}
        for row in self.app.db.list_media(limit=200000):counts[self.state(row)]+=1
        return dict(counts,checked=self.checked,checking=self.checking,error=self.error)
