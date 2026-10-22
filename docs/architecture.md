# Architecture

Scud discovers local media and sends a media list to Rex. During playback, Rex requests the original file from Scud over HTTP.

```text
Local folders -> Scan -> Match titles -> Read media details -> SQLite
                                                           |
                                                           v
                                                     Rex / Web UI

Rex playback -> HTTP Range request -> Scud -> Local file
```

## Components

- `scanner.py` checks configured folders and records changes; `publisher.py` persists and delivers those changes independently with debouncing and exponential backoff.
- `inventory.py` fingerprints each directory’s video names, sizes and modification times, bypassing unchanged folders while preserving deletion detection.
- `compat.py` checks Rex and TMDB API contracts at startup and stores the release compatibility record.
- `matcher.py` parses titles and episode numbers and searches TMDB. Folder and filename searches use the parsed media type and year.
- `probe.py` runs FFprobe to read media details. The scanner stores the result and repeats analysis when a file's size or modification time changes.
- `tmdb.py` searches movie and TV titles and validates the configured API credential.
- `rex.py` registers the source and sends additions, removals, and complete media lists to Rex.
- `web.py` serves the interface, API, and media files, including HTTP Range requests for seeking.
- `db.py` stores discovered files, cached searches, matches, media details, and sync history in SQLite.

The publisher stores pending work in SQLite. Acknowledgements remove only the job generation that was sent, so changes arriving during a request survive. Failed requests retain their jobs and schedule a full snapshot; a queue overflow also becomes a durable full-snapshot request.

## Scanning and recovery

Scud checks folders every 60 seconds by default. A complete media list is sent to Rex at startup and every six hours to recover from missed updates or connection problems.

If a configured folder is unavailable, Scud preserves its existing records rather than treating every file in it as deleted.
