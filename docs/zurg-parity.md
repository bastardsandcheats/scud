# Rex and Zurg compatibility

The tested Rex commit and test timestamp are recorded in `scud/rex_compatibility.json`, displayed in Settings, and summarised in the README. Compatibility checks exercise the configured running server rather than assuming that newer source code has already been installed.

## Covered feed behavior

Scud follows Rex’s `docs/feed-api.md` and the behavior of Zurg’s `internal/rexfeed/feed.go` and `internal/rexfeed/library.go`:

- Source registration and explicit destination library keys.
- Matched movie/show IDs, TV season/episode numbers and multi-episode end numbers.
- Full FFprobe streams, formats and chapters.
- Bonus videos as `kind: extra` clips with an `extra_type`, attached to a matched title.
- Upserts in batches of 200, removals in batches of 1,000 and complete chunked snapshots.
- A durable, bounded publishing queue, debouncing and exponential retry backoff, independent of scanning.
- Immediate restart from part zero when Rex loses a snapshot session. Shrink-guard refusals are not bypassed.
- HTTP GET, HEAD and byte ranges for playback. Source DELETE is optional and disabled by default.

Source paths and matching references are recorded in [NOTICE](../NOTICE.md) and the corresponding modules. Scud does not bundle Zurg or Rex source trees.

## Numbering and bonus videos

Scud parses common season/episode forms, including `S01EP02`, consecutive `S01E23.plus.EP24`, and bare episode numbers under explicit season directories. Numbered season-zero specials remain episodes. Unnumbered files in recognised bonus folders become clips; they are not assigned invented episode numbers. An extra requires a matched movie or episode in its media folder so Rex has a parent title to attach it to. Nonconsecutive or ambiguous numbering may require the episode picker.

Zurg can also obtain DMM’s per-file placement. Scud uses TMDB title searches, filename numbering and saved manual overrides. Exhaustive parity with DMM’s provider and anime placement is not claimed. Unmatched files remain withheld by design.

Archive, NZB and debrid-provider extraction are outside Scud’s scope. Serve extracted local video files instead.
