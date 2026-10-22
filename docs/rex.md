# Rex integration

Scud uses Rex's source/feed API to register its file server and send media lists. This is the same API Zurg uses to supply media to Rex.

## Connection

Set `rex_url` to the address and port of your Rex server. **Test Rex** checks `GET /rex/sources`. The source API accepts connections from local and private networks, including Tailscale.

## Source registration

Before sending media, Scud registers its file server:

```http
PUT /rex/sources/scud
Content-Type: application/json

{"url":"http://<scud-host>:8788/files","mount":"/scud"}
```

The source name comes from `rex_source`. When `source_url` is blank, Scud selects its local address from the connection to Rex. Set `source_url` manually if Rex needs a different address to reach Scud.

## Media updates

Only matched files with valid media IDs are published. TV episodes also require season and episode numbers. Recognised bonus videos are published as clips of a matched title in the same folder. Unmatched or incomplete files remain in Scud; entries previously published for those files are withdrawn from Rex.

```text
POST   /rex/feed/scud/items
DELETE /rex/feed/scud/items
PUT    /rex/feed/scud/snapshot
```

The independent publisher sends additions and changes in batches of 200 items and removals in batches of 1,000 IDs. A complete snapshot is sent at startup, after a failed update, and at the interval set by `rex_snapshot_every_hours`.

Rex can reject a snapshot that would remove more than half of a source's media. Scud reports that error and leaves the decision to the server administrator.

## Library selection

Each item identifies its destination by the saved Rex section key. The wizard creates or reuses the named libraries through Rex’s library API and saves their section IDs as `rex_library_key`. Each file is sent to its configured section.

## File playback

A file such as `movies/Alien (1979)/Alien (1979).mkv` is served at:

```text
http://<scud-host>:8788/files/movies/Alien%20(1979)/Alien%20(1979).mkv
```

Scud checks that the requested file is within its configured folder. It supports HTTP GET, HEAD, and single-range requests. Rex reads the original media file during playback.

Scud refuses source-side DELETE with HTTP 403 by default. If **Allow deletion from Rex** is enabled, deleting a registered file from a Rex client removes the original file and withdraws its source ID.

## Compatibility

At startup, Scud checks the Rex source/feed and library API response formats, including an isolated held item, and the TMDB configuration, movie/TV search and episode metadata formats. The temporary Rex source contains no playable media and is removed after the check. Failures appear in the log and the interface. These checks cover Scud’s API use; they cannot certify every Rex feature.

The last tested commit is recorded in `scud/rex_compatibility.json` and displayed in Settings and the README. Maintainers can record a new verified baseline with `python -m scud.compat --record --revision-file /path/to/installed-revision` after running the tests.

See [Zurg parity review](zurg-parity.md) for current differences.

## API references

- Rex: `docs/feed-api.md`
- Zurg: `internal/rexfeed/feed.go` and `internal/rexfeed/library.go`
