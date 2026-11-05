# Rex integration

Scud uses Rex's source/feed API to register its file server and send media lists. This is the same API Zurg uses to supply media to Rex.

## Connection

Set `rex_url` to the address and port of your Rex server. **Test Rex** checks `GET /rex/sources`. The source API accepts connections from local and private networks, including Tailscale.

## Source registration

Before sending media, Scud registers its file server:

```http
PUT /rex/sources/scud
Content-Type: application/json

{"url":"http://<scud-host>:8788/files","mount":"/scud",
 "directories":[{"name":"movies","movies":"Local Movies"},{"name":"tv","shows":"Local TV"}]}
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

## File identity and replacement

Scud keeps its local media row, saved matches and manual episode numbers when a file is renamed or replaced. Renaming unchanged media preserves its Rex feed ID. A changed size, modification time or replacement inode creates a new Rex version ID and a distinct logical file label, sends the fresh probe, and withdraws the old version through the publisher. The HTTP path still points to the actual local file. This prevents Rex from retaining the previous version's codecs and track layout. Timestamp-only changes are conservatively treated as a new version too.

On 23 October 2026, Scud was manually reviewed against [Building rex addons](https://notes.debridmediamanager.com/guides/rex-addons/) and Rex's feed API reference. Scud identifies existing movies/shows with external IDs, so it intentionally uses Plex metadata rather than addon `display` fields. Source registration, probing, placement, file sizes, snapshots, session recovery and optional deletion follow that contract.

The file-version correction is covered by regression tests for in-place and atomic replacements, equal-size replacements, repeated versions, renames, persisted version IDs, preserved manual matches/numbering, failed probes and bonus-clip labels. A disposable Rex executable from the installed build also accepted a replacement version and stored its new HEVC/1280-width probe. This review and the bounded metadata check do not certify every client or media format.

## Library selection

Each configured local root is declared as a native source directory with its movie or TV library name. Rex creates or reuses the library for that directory, then places items by their source paths. Roots with the same name and media type share a declared directory, with Scud routing their file requests to the correct local root. Existing feed IDs and logical file labels remain stable; single-root installs no longer send saved section keys as destination overrides. Existing shared libraries whose local roots all have the same saved section key retain that known destination, avoiding duplicate libraries or version-ID changes. Rex preserves names already assigned to existing libraries; rename those libraries in Rex.

## File playback

A file such as `movies/Alien (1979)/Alien (1979).mkv` is served at:

```text
http://<scud-host>:8788/files/movies/Alien%20(1979)/Alien%20(1979).mkv
```

Scud checks that the requested file is within its configured folder. It supports HTTP GET, HEAD, and single-range requests. Rex reads the original media file during playback.

Scud refuses source-side DELETE with HTTP 403 by default. If **Allow deletion from Rex** is enabled, deleting a registered file from a Rex client removes the original file and withdraws its source ID.

## Compatibility

At startup, Scud waits for `/identity`, then reads the native source listing schema and checks TMDB. It does not call `/library/sections`, which belongs to Rex’s separate authenticated Plex API. It does not create media, register test sources, or delete sources on the production Rex.

The machine-local Rex updater clones the exact candidate revision into a new directory, builds an unpatched upstream Rex and tests both claimed and unclaimed disposable instances, then builds and tests the locally patched candidate. Every instance uses an empty test catalogue. It runs the full Scud source/feed contract, including held-item creation/removal, snapshots and source deletion, against that instance. The container has an internal network, a host loopback proxy, dummy claim data where applicable, and no production configuration, media or credentials. The proxy never injects authentication headers; Scud must succeed without a token. It is destroyed before production is rebuilt. A failed check or failed cleanup prevents deployment. Native source declarations, held-item operations and snapshots are checked without using the Plex library API.

A successful validation receipt records the exact revision, build fingerprint and Scud checker digest. The post-deployment watcher verifies that receipt and records the baseline; it does not repeat mutating tests on production. These checks cover Scud's API use, not every client or media format.

The last tested commit is recorded in `scud/rex_compatibility.json` and displayed in Settings and the README. Maintainers can record a new verified baseline with `python -m scud.compat --record --receipt /path/to/isolated-validation.json --revision-file /path/to/installed-revision` after running the tests.

See [Zurg parity review](zurg-parity.md) for current differences.

## API references

- Rex: `docs/feed-api.md`
- Zurg: `internal/rexfeed/feed.go` and `internal/rexfeed/library.go`

## Reproduce against unpatched upstream

The integration tests accept a maintainer-built, unpatched Rex image; Scud does not ship a Docker installation. With an upstream test image and its matching pristine source checkout available:

```bash
REX_UPSTREAM_IMAGE=scud-rex-upstream REX_UPSTREAM_SOURCE=/path/to/pristine-rex python -m unittest discover -s tests -p test_upstream_rex.py -v
```

The tests run claimed and unclaimed isolated Rex instances, with no tokens added by the proxy. The Scud integration also registers shared libraries, publishes a cached matched movie, checks native receipts and verifies original file byte ranges both directly and through Rex. It also checks that an existing multi-root library retains its section and feed IDs. Authenticated Plex requests appear only in the test's final placement assertions and are never made by Scud. Containers, networks and temporary state are removed after each case.
