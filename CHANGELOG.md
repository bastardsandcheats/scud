# Changelog

## Unreleased

Fix HTTP 401 on stock Rex by declaring libraries and checking receipts exclusively through the native source/feed API, without tokens. Preserve feed identities and shared destinations across multiple local folders. Add unpatched claimed/unclaimed Rex integration tests and remove credential injection from isolated validation.

Give replaced local media a new Rex version and file label so Rex receives its updated codec and track metadata. Preserve Scud matches and manual episode numbering, keep unchanged rename identities stable, and handle atomic file replacements. Added replacement regression tests and documented a manual review against the Rex addon guide.

## 0.1.1

Save setup and settings locally without waiting for Rex. Library creation and source registration run through the durable background publisher, which retries when Rex is busy or unavailable.

## 0.1.0

Initial distribution release: local movie and TV libraries for Rex, TMDB matching and episode correction, bonus clips, cached media probing, folder change detection, persistent delivery with retries, startup compatibility checks, configurable logging, and a setup wizard with editable libraries. File deletion through Rex is opt-in and disabled by default.
