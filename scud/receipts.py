"""Verify accepted source items through the native Rex feed API."""
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
            # The native listing proves acceptance without entering the gated PMS API.
            # Preserve the expected file label check so an older version is not current.
            rows=self.app.db.list_media(limit=200000)
            expected={item['id']:item for item in self.app.scanner.feed_items(rows)}
            libraries={self.app.scanner.feed_id(row):row['library_id'] for row in rows}
            self.locations={item['id']:libraries[item['id']] for item in items
                            if item['id'] in expected and item.get('file')==(expected[item['id']].get('file') or '/scud/'+expected[item['id']]['path'])}
            self.library_names={library['id']:library.get('rex_library_name') or library.get('name','Rex library') for library in self.app.config.get('libraries',[])}
            self.checked=time.time();self.error=''
        except Exception as error:
            self.error=str(error)
            self.app.log.warning('Rex receipt check failed: %s',error)
        finally:self.checking=False

    def state(self,row):
        if not self.app.scanner.publishable(row):return 'withheld'
        if self.checked is None or self.error:return 'unknown'
        actual=self.locations.get(self.app.scanner.feed_id(row))
        target=row['library_id']
        if actual is None:return 'pending'
        return 'received' if target and actual==target else 'other_library'

    def summary(self):
        counts={state:0 for state in ('received','pending','withheld','other_library','unknown')}
        for row in self.app.db.list_media(limit=200000):counts[self.state(row)]+=1
        return dict(counts,checked=self.checked,checking=self.checking,error=self.error)
